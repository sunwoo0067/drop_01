"""
AI Agent Type Definitions

에이전트 노드별 입력/출력 타입 정의 (Pydantic 모델)
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
from enum import Enum


class ProcessingStatus(str, Enum):
    """가공 상태"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MarketType(str, Enum):
    """마켓플레이스 타입"""
    COUPANG = "Coupang"
    SMARTSTORE = "SmartStore"
    NAVER = "Naver"
    GMARKET = "Gmarket"
    ELEVENST = "11st"


# ============================================================================
# ProcessingAgent Types
# ============================================================================

class ExtractDetailsInput(BaseModel):
    """상세페이지 추출 입력"""
    name: str = Field(..., description="제품 이름")
    description: Optional[str] = Field(None, description="제품 설명")
    content: Optional[str] = Field(None, description="제품 콘텐츠")
    images: List[str] = Field(default_factory=list, description="이미지 URL 목록")
    category: Optional[str] = Field(None, description="카테고리")
    brand: Optional[str] = Field(None, description="브랜드명")
    target_market: Optional[MarketType] = Field(MarketType.COUPANG, description="타겟 마켓")


class ExtractDetailsOutput(BaseModel):
    """상세페이지 추출 출력"""
    normalized_detail: str = Field(..., description="정규화된 상세페이지 내용")
    extracted_fields: Dict[str, Any] = Field(default_factory=dict, description="추출된 추가 필드")
    original_text_length: int = Field(0, description="원본 텍스트 길이")
    normalized_text_length: int = Field(0, description="정규화된 텍스트 길이")


class OCRExtractionInput(BaseModel):
    """OCR 추출 입력"""
    images: List[str] = Field(..., description="이미지 URL 목록")
    detail_text: Optional[str] = Field(None, description="기존 상세페이지 텍스트")
    max_images: int = Field(2, description="처리할 최대 이미지 수")


class OCRExtractionOutput(BaseModel):
    """OCR 추출 출력"""
    ocr_texts: List[str] = Field(default_factory=list, description="추출된 OCR 텍스트 목록")
    combined_text: str = Field("", description="결합된 OCR 텍스트")
    processed_image_count: int = Field(0, description="처리된 이미지 수")
    failed_image_count: int = Field(0, description="실패한 이미지 수")


class SEOOptimizationInput(BaseModel):
    """SEO 최적화 입력"""
    name: str = Field(..., description="원본 제품명")
    brand: str = Field("", description="브랜드명")
    context: Optional[str] = Field(None, description="상세페이지 콘텐츠")
    benchmark_name: Optional[str] = Field(None, description="벤치마크 제품명")
    category: str = Field("일반", description="카테고리")
    market: MarketType = Field(MarketType.COUPANG, description="타겟 마켓")
    examples: List[Dict[str, str]] = Field(default_factory=list, description="Few-shot 예제")


class SEOOptimizationOutput(BaseModel):
    """SEO 최적화 출력"""
    processed_name: str = Field(..., description="최적화된 제품명")
    processed_keywords: List[str] = Field(default_factory=list, description="추출된 키워드 목록")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="최적화 신뢰도 점수")
    original_name: str = Field(..., description="원본 제품명")
    used_examples_count: int = Field(0, description="사용된 예제 수")


class ImageProcessingInput(BaseModel):
    """이미지 처리 입력"""
    product_id: str = Field(..., description="제품 ID")
    raw_images: List[str] = Field(..., description="원본 이미지 URL 목록")
    detail_html: Optional[str] = Field(None, description="상세페이지 HTML")


class ImageProcessingOutput(BaseModel):
    """이미지 처리 출력"""
    processed_image_urls: List[str] = Field(default_factory=list, description="처리된 이미지 URL 목록")
    processed_count: int = Field(0, description="처리된 이미지 수")
    failed_count: int = Field(0, description="실패한 이미지 수")


class ProcessingAgentOutput(BaseModel):
    """ProcessingAgent 최종 출력"""
    processed_name: str = Field(..., description="최적화된 제품명")
    processed_keywords: List[str] = Field(default_factory=list, description="추출된 키워드 목록")
    processed_image_urls: List[str] = Field(default_factory=list, description="처리된 이미지 URL 목록")
    status: ProcessingStatus = Field(ProcessingStatus.COMPLETED, description="처리 상태")
    error_message: Optional[str] = Field(None, description="에러 메시지")


# ============================================================================
# SourcingAgent Types
# ============================================================================

class BenchmarkAnalysisInput(BaseModel):
    """벤치마크 분석 입력"""
    name: str = Field(..., description="벤치마크 제품명")
    detail_html: Optional[str] = Field(None, description="상세페이지 HTML")
    images: List[str] = Field(default_factory=list, description="이미지 URL 목록")
    reviews: List[str] = Field(default_factory=list, description="리뷰 목록")
    price: Optional[float] = Field(None, description="가격")


class BenchmarkAnalysisOutput(BaseModel):
    """벤치마크 분석 출력"""
    pain_points: List[str] = Field(default_factory=list, description="고객 불만사항 목록")
    specs: Dict[str, Any] = Field(default_factory=dict, description="제품 스펙")
    visual_analysis: str = Field("", description="시각적 분석 결과")
    analysis_timestamp: Optional[str] = Field(None, description="분석 시간")


class SupplierItem(BaseModel):
    """공급처 항목"""
    item_code: str = Field(..., description="항목 코드")
    name: str = Field(..., description="항목 이름")
    supply_price: float = Field(..., ge=0, description="공급가")
    thumbnail_url: Optional[str] = Field(None, description="썸네일 URL")
    is_vector_match: bool = Field(False, description="벡터 검색 매칭 여부")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="유사도 점수")
    seasonal_score: float = Field(0.0, ge=0.0, le=1.0, description="시즌성 점수")
    expert_match_score: float = Field(0.0, ge=0.0, le=1.0, description="전문가 매칭 점수")
    expert_match_reason: str = Field("", description="전문가 매칭 사유")
    item_name: Optional[str] = Field(None, description="대체 항목 이름 필드")
    itemCode: Optional[str] = Field(None, description="대체 항목 코드 필드")


class SupplierSearchInput(BaseModel):
    """공급처 검색 입력"""
    query: str = Field(..., description="검색 쿼리")
    benchmark_id: Optional[str] = Field(None, description="벤치마크 ID")
    limit: int = Field(30, ge=1, le=100, description="검색 결과 제한")
    use_vector_search: bool = Field(True, description="벡터 검색 사용 여부")


class SupplierSearchOutput(BaseModel):
    """공급처 검색 출력"""
    items: List[SupplierItem] = Field(default_factory=list, description="검색된 항목 목록")
    api_count: int = Field(0, description="API 검색 결과 수")
    vector_count: int = Field(0, description="벡터 검색 결과 수")
    total_count: int = Field(0, description="총 결과 수")


class CandidateScoringInput(BaseModel):
    """후보 점수 부여 입력"""
    candidates: List[SupplierItem] = Field(..., description="후보 항목 목록")
    benchmark_id: Optional[str] = Field(None, description="벤치마크 ID")


class CandidateScoringOutput(BaseModel):
    """후보 점수 부여 출력"""
    scored_candidates: List[SupplierItem] = Field(..., description="점수가 부여된 후보 목록")
    scoring_timestamp: Optional[str] = Field(None, description="점수 부여 시간")


class CandidateRankingInput(BaseModel):
    """후보 랭킹 입력"""
    candidates: List[SupplierItem] = Field(..., description="후보 항목 목록")
    benchmark_specs: Dict[str, Any] = Field(default_factory=dict, description="벤치마크 스펙")
    benchmark_visual: str = Field("", description="벤치마크 시각적 분석")
    max_candidates: int = Field(7, ge=1, le=20, description="랭킹 분석할 최대 후보 수")


class RankingResult(BaseModel):
    """랭킹 결과"""
    id: str = Field(..., description="항목 ID")
    score: float = Field(..., ge=0.0, le=1.0, description="매칭 점수")
    reason: str = Field(..., description="매칭 사유")


class CandidateRankingOutput(BaseModel):
    """후보 랭킹 출력"""
    ranked_candidates: List[SupplierItem] = Field(..., description="랭킹된 후보 목록")
    rankings: List[RankingResult] = Field(default_factory=list, description="랭킹 결과 목록")
    expert_summary: str = Field("", description="전문가 요약")


class SourcingAgentOutput(BaseModel):
    """SourcingAgent 최종 출력"""
    candidates: List[SupplierItem] = Field(default_factory=list, description="최종 후보 목록")
    candidate_count: int = Field(0, description="후보 수")
    benchmark_analysis: Optional[BenchmarkAnalysisOutput] = Field(None, description="벤치마크 분석 결과")
    expert_summary: str = Field("", description="전문가 요약")
    status: ProcessingStatus = Field(ProcessingStatus.COMPLETED, description="처리 상태")
    error_message: Optional[str] = Field(None, description="에러 메시지")


# ============================================================================
# Common Types
# ============================================================================

class WorkflowStepResult(BaseModel):
    """워크플로우 단계 결과"""
    step_name: str = Field(..., description="단계 이름")
    status: ProcessingStatus = Field(..., description="처리 상태")
    duration_ms: Optional[float] = Field(None, description="소요 시간 (밀리초)")
    error_message: Optional[str] = Field(None, description="에러 메시지")
    output: Optional[Dict[str, Any]] = Field(None, description="출력 데이터")


class WorkflowExecutionResult(BaseModel):
    """워크플로우 실행 결과"""
    job_id: str = Field(..., description="작업 ID")
    workflow_name: str = Field(..., description="워크플로우 이름")
    status: ProcessingStatus = Field(..., description="최종 상태")
    steps: List[WorkflowStepResult] = Field(default_factory=list, description="단계별 결과")
    final_output: Optional[Dict[str, Any]] = Field(None, description="최종 출력")
    error_message: Optional[str] = Field(None, description="에러 메시지")
    start_time: Optional[str] = Field(None, description="시작 시간")
    end_time: Optional[str] = Field(None, description="종료 시간")


class FewShotExample(BaseModel):
    """Few-shot 예제"""
    original: str = Field(..., description="원본 이름")
    processed: str = Field(..., description="가공된 이름")
    category: Optional[str] = Field(None, description="카테고리")
    market: Optional[MarketType] = Field(None, description="마켓")


class SeasonalityData(BaseModel):
    """시즌성 데이터"""
    current_month_score: float = Field(..., ge=0.0, le=1.0, description="현재 월 점수")
    peak_months: List[int] = Field(default_factory=list, description="피크 시기 (월)")
    off_peak_months: List[int] = Field(default_factory=list, description="비수기 (월)")
    seasonality_reason: str = Field("", description="시즌성 사유")


# ============================================================================
# Validators
# ============================================================================

class BaseValidator:
    """공통 유효성 검사기"""
    
    @staticmethod
    def validate_item_code(value: str) -> str:
        """항목 코드 유효성 검사"""
        if not value or not value.strip():
            raise ValueError("item_code cannot be empty")
        return value.strip()
    
    @staticmethod
    def validate_price(value: float) -> float:
        """가격 유효성 검사"""
        if value < 0:
            raise ValueError("price cannot be negative")
        return round(value, 2)
    
    @staticmethod
    def validate_url(value: Optional[str]) -> Optional[str]:
        """URL 유효성 검사"""
        if not value:
            return None
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value


# ============================================================================
# Helper Functions
# ============================================================================

def to_dict_safe(obj: BaseModel) -> Dict[str, Any]:
    """Pydantic 모델을 안전하게 딕셔너리로 변환"""
    if obj is None:
        return {}
    return obj.model_dump(exclude_none=True)


def from_dict_safe(cls: type, data: Dict[str, Any]) -> Optional[BaseModel]:
    """딕셔너리를 안전하게 Pydantic 모델로 변환"""
    try:
        return cls(**data)
    except Exception:
        return None
