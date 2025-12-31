"""
Workflow Router

동적 워크플로우 라우팅을 위한 클래스
"""
import logging
from typing import Dict, Callable, Optional, List, Any
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
    """
    
    def __init__(self):
        self.routes: Dict[str, Callable] = {}
        self.conditions: Dict[str, Dict[str, Any]] = {}
        self.default_routes: Dict[str, str] = {}
        self.error_route: Optional[str] = None
        self.retry_routes: Dict[str, Dict[str, Any]] = {}
    
    def register_node(self, name: str, handler: Callable) -> None:
        self.routes[name] = handler
        logger.debug(f"Registered node: {name}")
    
    def register_condition(
        self, 
        name: str, 
        condition: Callable[[AgentState], bool],
        condition_type: RoutingCondition = RoutingCondition.CUSTOM
    ) -> None:
        self.conditions[name] = {
            "func": condition,
            "type": condition_type
        }
        logger.debug(f"Registered condition: {name} ({condition_type.value})")
    
    def set_default_route(self, from_node: str, to_node: str) -> None:
        self.default_routes[from_node] = to_node
        logger.debug(f"Set default route: {from_node} -> {to_node}")
    
    def set_error_route(self, node_name: str) -> None:
        self.error_route = node_name
        logger.debug(f"Set error route: {node_name}")
    
    def set_retry_route(self, from_node: str, to_node: str, max_retries: int = 3) -> None:
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
        """
        # Debug logging
        logger.info(f"[Router] current_step: '{current_step}', state.current_step (from dict): {state.get('current_step')}")
        
        # 1. 명시적 next_step 확인
        explicit_next = state.get("next_step")
        if explicit_next and explicit_next != "":
            logger.info(f"[Router] Using explicit next_step: {explicit_next}")
            return explicit_next
        
        # 2. 에러가 있는 경우 에러 라우트로 (빈 리스트 [] 는 정상)
        errors = state.get("errors", [])
        if errors and len(errors) > 0:
            if self.error_route:
                logger.info(f"[Router] Routing to error handler: {self.error_route}")
                return self.error_route
            return "END"
        
        # 3. 조건부 분기 확인
        for condition_name, condition_data in self.conditions.items():
            condition_func = condition_data["func"]
            try:
                if condition_func(state):
                    route_target = self._find_route_for_condition(condition_name)
                    if route_target:
                        logger.info(f"[Router] Condition '{condition_name}' matched, routing to: {route_target}")
                        return route_target
            except Exception as e:
                logger.error(f"[Router] Error evaluating condition '{condition_name}': {e}")
        
        # 4. 재시도 로직 확인
        if current_step in self.retry_routes:
            retry_config = self.retry_routes[current_step]
            retry_count = state.get("retry_count", {}).get(current_step, 0)
            if retry_count < retry_config["max_retries"]:
                logger.info(f"[Router] Retrying {current_step} (attempt {retry_count + 1})")
                return current_step

        # 5. 기본 라우팅 확인
        next_step = self.default_routes.get(current_step)
        if next_step:
            logger.info(f"[Router] Routing from {current_step} to {next_step} by default")
            return next_step
        
        logger.warning(f"[Router] No route found for {current_step}, ending workflow")
        return "END"

    def _find_route_for_condition(self, condition_name: str) -> Optional[str]:
        if condition_name.startswith("route_to_"):
            return condition_name.replace("route_to_", "")
        return None

def create_sourcing_router() -> WorkflowRouter:
    router = WorkflowRouter()
    router.set_default_route("analyze_benchmark", "search_supplier")
    router.set_default_route("search_supplier", "score_candidates")
    router.set_default_route("score_candidates", "rank_candidates")
    router.set_default_route("rank_candidates", "finalize")
    router.set_default_route("finalize", "END")
    router.set_error_route("error_handler")
    return router

def create_processing_router() -> WorkflowRouter:
    router = WorkflowRouter()
    router.set_default_route("extract_details", "extract_ocr_details")
    router.set_default_route("extract_ocr_details", "optimize_seo")
    router.set_default_route("optimize_seo", "process_images")
    router.set_default_route("process_images", "save_product")
    router.set_default_route("save_product", "END")
    return router

def create_cs_router() -> WorkflowRouter:
    router = WorkflowRouter()
    router.set_default_route("analyze_inquiry", "retrieve_knowledge")
    router.set_default_route("retrieve_knowledge", "generate_draft")
    router.set_default_route("generate_draft", "self_review")
    router.set_default_route("self_review", "finalize")
    router.set_default_route("finalize", "END")
    return router

class ConditionalEdge:
    def __init__(self, router: WorkflowRouter):
        self.router = router
    def __call__(self, state: AgentState) -> str:
        """상태에 따라 다음 노드 결정"""
        current_step = state.get("current_step", "")
        # logger.info(f"[Router] Routing from {current_step}")
        return self.router.get_next_step(state, current_step)
