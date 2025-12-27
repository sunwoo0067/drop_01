"""
Workflow Router

동적 워크플로우 라우팅을 위한 클래스
"""
import logging
from typing import Dict, Callable, Optional, List
from enum import Enum

from app.services.ai.agents.state import AgentState

logger = logging.getLogger(__name__)


class RoutingCondition(str, Enum):
    """라우팅 조건 타입"""
    ALWAYS = "always"
    ON_ERROR = "on_error"
    ON_SUCCESS = "on_success"
    CUSTOM = "custom"


class WorkflowRouter:
    """
    동적 워크플로우 라우터
    
    상태 기반 조건부 분기를 지원합니다.
    
    Attributes:
        routes: 노드 이름과 함수의 매핑
        conditions: 조건 이름과 함수의 매핑
        default_routes: 기본 라우팅 규칙
    """
    
    def __init__(self):
        self.routes: Dict[str, Callable] = {}
        self.conditions: Dict[str, Callable[[AgentState], bool]] = {}
        self.default_routes: Dict[str, str] = {}
        self.error_route: Optional[str] = None
        self.retry_routes: Dict[str, str] = {}
    
    def register_node(self, name: str, handler: Callable) -> None:
        """
        노드 등록
        
        Args:
            name: 노드 이름
            handler: 노드 핸들러 함수
        """
        self.routes[name] = handler
        logger.debug(f"Registered node: {name}")
    
    def register_condition(
        self, 
        name: str, 
        condition: Callable[[AgentState], bool],
        condition_type: RoutingCondition = RoutingCondition.CUSTOM
    ) -> None:
        """
        조건부 분기 등록
        
        Args:
            name: 조건 이름
            condition: 조건 함수 (상태를 받아 bool 반환)
            condition_type: 조건 타입
        """
        self.conditions[name] = {
            "func": condition,
            "type": condition_type
        }
        logger.debug(f"Registered condition: {name} ({condition_type.value})")
    
    def set_default_route(self, from_node: str, to_node: str) -> None:
        """
        기본 라우팅 규칙 설정
        
        Args:
            from_node: 출발 노드
            to_node: 도착 노드
        """
        self.default_routes[from_node] = to_node
        logger.debug(f"Set default route: {from_node} -> {to_node}")
    
    def set_error_route(self, node_name: str) -> None:
        """
        에러 처리 라우트 설정
        
        Args:
            node_name: 에러 처리 노드 이름
        """
        self.error_route = node_name
        logger.debug(f"Set error route: {node_name}")
    
    def set_retry_route(self, from_node: str, to_node: str, max_retries: int = 3) -> None:
        """
        재시도 라우트 설정
        
        Args:
            from_node: 출발 노드
            to_node: 재시시할 노드
            max_retries: 최대 재시도 횟수
        """
        self.retry_routes[from_node] = {
            "target": to_node,
            "max_retries": max_retries
        }
        logger.debug(f"Set retry route: {from_node} -> {to_node} (max {max_retries} retries)")
    
    def get_next_step(
        self, 
        state: AgentState, 
        current_step: str,
        verbose: bool = False
    ) -> str:
        """
        다음 단계 결정
        
        Args:
            state: 현재 에이전트 상태
            current_step: 현재 단계 이름
            verbose: 상세 로깅 여부
        
        Returns:
            다음 단계 이름
        """
        # 1. 명시적 next_step 확인
        explicit_next = state.get("next_step")
        if explicit_next and explicit_next != "":
            if verbose:
                logger.info(f"[Router] Using explicit next_step: {explicit_next}")
            return explicit_next
        
        # 2. 에러가 있는 경우 에러 라우트로
        if state.get("errors"):
            if self.error_route:
                if verbose:
                    logger.info(f"[Router] Routing to error handler: {self.error_route}")
                return self.error_route
            # 에러 라우트가 없으면 종료
            if verbose:
                logger.warning(f"[Router] No error route defined, ending workflow")
            return "END"
        
        # 3. 조건부 분기 확인
        for condition_name, condition_data in self.conditions.items():
            condition_func = condition_data["func"]
            condition_type = condition_data["type"]
            
            try:
                should_route = condition_func(state)
                
                if should_route:
                    # 조건에 맞는 라우트 찾기
                    route_target = self._find_route_for_condition(condition_name)
                    if route_target:
                        if verbose:
                            logger.info(f"[Router] Condition '{condition_name}' matched, routing to: {route_target}")
                        return route_target
            except Exception as e:
                logger.error(f"[Router] Error evaluating condition '{condition_name}': {e}")
        
        # 4. 재시도 로직 확인
        if current_step in self.retry_routes:
            retry_config = self.retry_routes[current_step]
            retry_count = state.get("retry_count", {}).get(current_step, 0)
            
            if retry_count < retry_config["max_retries"]:
                if verbose:
                    logger.info(f"[Router] Retrying {current_step} (attempt {retry_count + 1}/{retry_config['max_retries']})")
                # 재시도 카운트 증가
                if "retry_count" not in state:
                    state["retry_count"] = {}
                state["retry_count"][current_step] = retry_count + 1
                return retry_config["target"]
        
        # 5. 기본 라우팅
        default_next = self.default_routes.get(current_step, "END")
        if verbose:
            logger.info(f"[Router] Using default route: {current_step} -> {default_next}")
        return default_next
    
    def _find_route_for_condition(self, condition_name: str) -> Optional[str]:
        """
        조건 이름에 해당하는 라우트 찾기
        
        Args:
            condition_name: 조건 이름
        
        Returns:
            라우트 타겟 노드 이름
        """
        # 조건 이름에서 타겟 노드 추출 (예: "route_to_finalize" -> "finalize")
        if condition_name.startswith("route_to_"):
            return condition_name.replace("route_to_", "")
        return None
    
    def get_all_routes(self) -> Dict[str, str]:
        """
        모든 라우트 반환
        
        Returns:
            라우트 딕셔너리
        """
        routes = self.default_routes.copy()
        if self.error_route:
            routes["error"] = self.error_route
        return routes


class ConditionalEdge:
    """
    조건부 엣지 정의
    
    LangGraph의 conditional_edge를 쉽게 정의하기 위한 헬퍼 클래스
    """
    
    def __init__(self, router: WorkflowRouter):
        """
        조건부 엣지 초기화
        
        Args:
            router: 워크플로우 라우터
        """
        self.router = router
    
    def __call__(self, state: AgentState) -> str:
        """
        상태에 따라 다음 노드 결정
        
        Args:
            state: 에이전트 상태
        
        Returns:
            다음 노드 이름
        """
        current_step = state.get("current_step", "")
        return self.router.get_next_step(state, current_step)


# ============================================================================
# 사전 정의된 조건들
# ============================================================================

def has_errors(state: AgentState) -> bool:
    """에러가 있는지 확인"""
    errors = state.get("errors", [])
    return len(errors) > 0


def has_collected_items(state: AgentState) -> bool:
    """수집된 항목이 있는지 확인"""
    items = state.get("collected_items", [])
    return len(items) > 0


def has_candidate_results(state: AgentState) -> bool:
    """후보 결과가 있는지 확인"""
    candidates = state.get("candidate_results", [])
    return len(candidates) > 0


def has_benchmark_data(state: AgentState) -> bool:
    """벤치마크 데이터가 있는지 확인"""
    benchmark = state.get("benchmark_data")
    return benchmark is not None and len(benchmark) > 0


def has_final_output(state: AgentState) -> bool:
    """최종 출력이 있는지 확인"""
    output = state.get("final_output")
    return output is not None and len(output) > 0


def is_name_only_processing(state: AgentState) -> bool:
    """이름 전용 처리 모드인지 확인"""
    input_data = state.get("input_data", {})
    return input_data.get("name_only", False)


def has_images(state: AgentState) -> bool:
    """이미지가 있는지 확인"""
    input_data = state.get("input_data", {})
    images = input_data.get("images", [])
    return len(images) > 0


def has_ocr_text(state: AgentState) -> bool:
    """OCR 텍스트가 있는지 확인"""
    input_data = state.get("input_data", {})
    detail = input_data.get("normalized_detail", "")
    return "[OCR Data]" in detail


def min_items_collected(min_count: int = 1):
    """
    최소 항목 수 조건 팩토리
    
    Args:
        min_count: 최소 항목 수
    
    Returns:
        조건 함수
    """
    def condition(state: AgentState) -> bool:
        items = state.get("collected_items", [])
        return len(items) >= min_count
    return condition


def max_items_collected(max_count: int = 10):
    """
    최대 항목 수 조건 팩토리
    
    Args:
        max_count: 최대 항목 수
    
    Returns:
        조건 함수
    """
    def condition(state: AgentState) -> bool:
        items = state.get("collected_items", [])
        return len(items) <= max_count
    return condition


def score_above_threshold(threshold: float = 0.7):
    """
    점수 임계값 조건 팩토리
    
    Args:
        threshold: 점수 임계값
    
    Returns:
        조건 함수
    """
    def condition(state: AgentState) -> bool:
        candidates = state.get("candidate_results", [])
        if not candidates:
            return False
        # 최고 점수 확인
        top_score = max(
            (c.get("expert_match_score", 0) for c in candidates),
            default=0
        )
        return top_score >= threshold
    return condition


# ============================================================================
# 사전 정의된 라우터
# ============================================================================

def create_sourcing_router() -> WorkflowRouter:
    """
    SourcingAgent용 라우터 생성
    
    Returns:
        WorkflowRouter 인스턴스
    """
    router = WorkflowRouter()
    
    # 기본 라우팅
    router.set_default_route("analyze_benchmark", "search_supplier")
    router.set_default_route("search_supplier", "score_candidates")
    router.set_default_route("score_candidates", "rank_candidates")
    router.set_default_route("rank_candidates", "finalize")
    router.set_default_route("finalize", "END")
    
    # 에러 라우트
    router.set_error_route("error_handler")
    
    return router


def create_processing_router() -> WorkflowRouter:
    """
    ProcessingAgent용 라우터 생성
    
    Returns:
        WorkflowRouter 인스턴스
    """
    router = WorkflowRouter()
    
    # 기본 라우팅
    router.set_default_route("extract_details", "extract_ocr_details")
    router.set_default_route("extract_ocr_details", "optimize_seo")
    router.set_default_route("optimize_seo", "process_images")
    router.set_default_route("process_images", "save_product")
    router.set_default_route("save_product", "END")
    
    # 조건부 분기: 이름 전용 처리 모드
    router.register_condition(
        "name_only_processing",
        is_name_only_processing,
        RoutingCondition.CUSTOM
    )
    router.set_default_route("optimize_seo", "save_product")  # 조건에 따라 오버라이드
    
    # 에러 라우트
    router.set_error_route("error_handler")
    
    return router


# ============================================================================
# 라우터 헬퍼 함수
# ============================================================================

def setup_workflow_edges(
    workflow: 'StateGraph',
    router: WorkflowRouter,
    entry_point: str
) -> None:
    """
    워크플로우 엣지 설정
    
    Args:
        workflow: LangGraph StateGraph
        router: 워크플로우 라우터
        entry_point: 진입점 노드 이름
    """
    # 진입점 설정
    workflow.set_entry_point(entry_point)
    
    # 노드 등록
    for node_name, handler in router.routes.items():
        workflow.add_node(node_name, handler)
    
    # 기본 엣지 설정
    for from_node, to_node in router.default_routes.items():
        workflow.add_edge(from_node, to_node)
