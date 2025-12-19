from typing import Annotated, List, Dict, Any, Optional
from typing_extensions import TypedDict
import operator

class AgentState(TypedDict):
    """
    LangGraph 에이전트들이 공유하는 상태 클래스.
    """
    # 기본 메타데이터
    job_id: str
    target_id: str # Product ID or Benchmark ID
    
    # 데이터 영역
    input_data: Dict[str, Any]
    benchmark_data: Optional[Dict[str, Any]]
    collected_items: Annotated[List[Dict[str, Any]], operator.add]
    candidate_results: Annotated[List[Dict[str, Any]], operator.add]
    
    # 분석 결과
    pain_points: List[str]
    specs: Dict[str, Any]
    seasonality: Dict[str, Any]
    
    # 워크플로우 제어
    next_step: str
    errors: Annotated[List[str], operator.add]
    logs: Annotated[List[str], operator.add]
    
    # 최종 결과물
    final_output: Optional[Dict[str, Any]]
