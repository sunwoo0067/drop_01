"""
Base Agent Class

AI 에이전트의 공통 기능을 제공하는 베이스 클래스
"""
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from abc import ABC, abstractmethod
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.services.ai import AIService
from app.services.ai.agents.state import AgentState
from app.services.ai.exceptions import (
    AgentError, 
    WorkflowError, 
    wrap_exception,
    ErrorSeverity
)
from app.services.ai.agents.types import (
    ProcessingStatus,
    WorkflowExecutionResult,
    WorkflowStepResult
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    공통 에이전트 베이스 클래스
    
    모든 에이전트는 이 클래스를 상속받아 구현해야 합니다.
    
    Attributes:
        db: 데이터베이스 세션
        name: 에이전트 이름
        ai_service: AI 서비스 인스턴스
        workflow: LangGraph 워크플로우
    """
    
    def __init__(self, db: Session, name: str):
        """
        베이스 에이전트 초기화
        
        Args:
            db: 데이터베이스 세션
            name: 에이전트 이름
        """
        self.db = db
        self.name = name
        self.ai_service = AIService()
        self.workflow = self._create_workflow()
        self._step_results: List[WorkflowStepResult] = []
    
    @abstractmethod
    def _create_workflow(self) -> StateGraph:
        """
        워크플로우 생성
        
        Returns:
            LangGraph StateGraph 인스턴스
        """
        raise NotImplementedError("Subclasses must implement _create_workflow")
    
    @abstractmethod
    def _get_entry_point(self) -> str:
        """
        진입점 노드 이름 반환
        
        Returns:
            진입점 노드 이름
        """
        raise NotImplementedError("Subclasses must implement _get_entry_point")
    
    @abstractmethod
    def _get_nodes(self) -> Dict[str, Callable]:
        """
        노드 이름과 함수 매핑 반환
        
        Returns:
            노드 이름과 함수의 딕셔너리
        """
        raise NotImplementedError("Subclasses must implement _get_nodes")
    
    @abstractmethod
    def _create_initial_state(self, target_id: str, input_data: Dict[str, Any], **kwargs) -> AgentState:
        """
        초기 상태 생성
        
        Args:
            target_id: 타겟 ID
            input_data: 입력 데이터
            **kwargs: 추가 데이터 (에이전트별 특화 데이터)
        
        Returns:
            초기 AgentState
        """
        raise NotImplementedError("Subclasses must implement _create_initial_state")
    
    def _get_default_next(self, current_step: str) -> str:
        """
        기본 다음 단계 반환
        
        Args:
            current_step: 현재 단계 이름
        
        Returns:
            다음 단계 이름
        """
        # 서브클래스에서 오버라이드 가능
        return "END"
    
    async def run(
        self, 
        target_id: str, 
        input_data: Dict[str, Any],
        verbose: bool = False,
        **kwargs
    ) -> WorkflowExecutionResult:
        """
        워크플로우 실행
        
        Args:
            target_id: 타겟 ID
            input_data: 입력 데이터
            verbose: 상세 로깅 여부
            **kwargs: 추가 데이터 (에이전트별 특화 데이터)
        
        Returns:
            WorkflowExecutionResult 인스턴스
        """
        self._step_results = []
        start_time = time.time()
        start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
        
        if verbose:
            self.log_step("start", f"Starting workflow for {self.name} with target_id={target_id}")
        
        initial_state = self._create_initial_state(target_id, input_data, **kwargs)
        
        try:
            result = await self.workflow.ainvoke(initial_state)
            
            end_time = time.time()
            end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
            duration_ms = (end_time - start_time) * 1000
            
            if verbose:
                self.log_step("complete", f"Workflow completed for {self.name} in {duration_ms:.2f}ms")
            
            # 에러가 있는 경우 상태를 FAILED로 설정
            status = ProcessingStatus.COMPLETED
            error_message = None
            if result.get("errors"):
                status = ProcessingStatus.FAILED
                error_message = "; ".join(result.get("errors", []))
            
            return WorkflowExecutionResult(
                job_id=result.get("job_id", ""),
                workflow_name=self.name,
                status=status,
                steps=self._step_results,
                final_output=result.get("final_output"),
                error_message=error_message,
                start_time=start_time_str,
                end_time=end_time_str
            )
            
        except Exception as e:
            end_time = time.time()
            end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
            duration_ms = (end_time - start_time) * 1000
            
            wrapped_error = wrap_exception(e, WorkflowError, workflow_name=self.name)
            self.handle_error(wrapped_error, "workflow_execution")
            
            return WorkflowExecutionResult(
                job_id=initial_state.get("job_id", ""),
                workflow_name=self.name,
                status=ProcessingStatus.FAILED,
                steps=self._step_results,
                error_message=str(wrapped_error),
                start_time=start_time_str,
                end_time=end_time_str
            )
    
    def log_step(self, step: str, message: str, level: str = "info"):
        """
        단계별 로깅
        
        Args:
            step: 단계 이름
            message: 로그 메시지
            level: 로그 레벨 (info, warning, error)
        """
        log_message = f"[{self.name}] [{step}] {message}"
        
        if level == "error":
            logger.error(log_message)
        elif level == "warning":
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def handle_error(self, error: AgentError, step: str):
        """
        에러 처리
        
        Args:
            error: 에이전트 에러
            step: 에러가 발생한 단계
        """
        error_msg = f"{step}: {str(error)}"
        logger.error(f"[{self.name}] {error_msg}")
        
        # 에러 심각도에 따른 추가 처리
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"[{self.name}] CRITICAL ERROR: {error.to_dict()}")
        
        # 복구 가능한 에러인 경우 폴백 로직 시도
        if error.recoverable:
            logger.info(f"[{self.name}] Attempting recovery for recoverable error")
            # 서브클래스에서 오버라이드하여 복구 로직 구현
            self._attempt_recovery(error, step)
    
    def _attempt_recovery(self, error: AgentError, step: str) -> bool:
        """
        에러 복구 시도
        
        Args:
            error: 에이전트 에러
            step: 에러가 발생한 단계
        
        Returns:
            복구 성공 여부
        """
        # 기본 구현: 복구 불가
        logger.warning(f"[{self.name}] No recovery logic implemented for {step}")
        return False
    
    def _record_step_result(
        self,
        step_name: str,
        status: ProcessingStatus,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        output: Optional[Dict[str, Any]] = None
    ):
        """
        단계 결과 기록
        
        Args:
            step_name: 단계 이름
            status: 처리 상태
            duration_ms: 소요 시간 (밀리초)
            error_message: 에러 메시지
            output: 출력 데이터
        """
        result = WorkflowStepResult(
            step_name=step_name,
            status=status,
            duration_ms=duration_ms,
            error_message=error_message,
            output=output
        )
        self._step_results.append(result)
    
    def _wrap_node_execution(self, node_name: str, node_func: Callable, state: AgentState) -> Dict[str, Any]:
        """
        노드 실행 래퍼 (에러 처리 및 로깅 포함)
        
        Args:
            node_name: 노드 이름
            node_func: 노드 함수
            state: 현재 상태
        
        Returns:
            노드 실행 결과
        """
        start_time = time.time()
        self.log_step(node_name, f"Starting execution")
        
        try:
            result = node_func(state)
            duration_ms = (time.time() - start_time) * 1000
            
            self._record_step_result(
                step_name=node_name,
                status=ProcessingStatus.COMPLETED,
                duration_ms=duration_ms,
                output=result
            )
            
            self.log_step(node_name, f"Completed in {duration_ms:.2f}ms")
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            wrapped_error = wrap_exception(e, AgentError)
            
            self._record_step_result(
                step_name=node_name,
                status=ProcessingStatus.FAILED,
                duration_ms=duration_ms,
                error_message=str(wrapped_error)
            )
            
            self.log_step(node_name, f"Failed: {str(wrapped_error)}", level="error")
            raise wrapped_error
    
    def _validate_state(self, state: AgentState, required_fields: List[str]) -> None:
        """
        상태 유효성 검사
        
        Args:
            state: 에이전트 상태
            required_fields: 필수 필드 목록
        
        Raises:
            ValidationError: 필수 필드가 누락된 경우
        """
        from app.services.ai.exceptions import ValidationError
        
        missing_fields = [field for field in required_fields if field not in state or state[field] is None]
        if missing_fields:
            raise ValidationError(
                f"Missing required fields in state: {', '.join(missing_fields)}",
                context={"missing_fields": missing_fields, "available_fields": list(state.keys())}
            )
    
    def _merge_state_updates(self, state: AgentState, updates: Dict[str, Any]) -> AgentState:
        """
        상태 업데이트 병합
        
        Args:
            state: 현재 상태
            updates: 업데이트할 데이터
        
        Returns:
            병합된 상태
        """
        merged = state.copy()
        
        for key, value in updates.items():
            # 리스트 필드는 병합
            if key in ["errors", "logs", "collected_items", "candidate_results", "pain_points"]:
                if key not in merged:
                    merged[key] = []
                if isinstance(value, list):
                    merged[key].extend(value)
                else:
                    merged[key].append(value)
            # 딕셔너리 필드는 병합
            elif key in ["specs", "seasonality"]:
                if key not in merged:
                    merged[key] = {}
                if isinstance(value, dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
            # 기타 필드는 덮어쓰기
            else:
                merged[key] = value
        
        return merged
    
    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """
        설정 값 조회
        
        Args:
            key: 설정 키
            default: 기본값
        
        Returns:
            설정 값
        """
        from app.settings import settings
        return getattr(settings, key, default)


class RetryMixin:
    """
    재시도 로직 믹스인 클래스
    
    에이전트에 재시도 기능을 추가하기 위해 사용합니다.
    """
    
    async def _retry_with_backoff(
        self,
        func: Callable,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        backoff_multiplier: float = 2.0,
        retry_on: tuple = (Exception,)
    ) -> Any:
        """
        백오프와 함께 재시도
        
        Args:
            func: 실행할 함수
            max_retries: 최대 재시도 횟수
            initial_backoff: 초기 백오프 시간 (초)
            backoff_multiplier: 백오프 승수
            retry_on: 재시도할 예외 타입 튜플
        
        Returns:
            함수 실행 결과
        
        Raises:
            마지막 시도에서 발생한 예외
        """
        import asyncio
        
        last_exception = None
        backoff = initial_backoff
        
        for attempt in range(max_retries + 1):
            try:
                return await func()
            except retry_on as e:
                last_exception = e
                
                if attempt < max_retries:
                    logger.warning(f"Retry attempt {attempt + 1}/{max_retries} after {backoff}s: {str(e)}")
                    await asyncio.sleep(backoff)
                    backoff *= backoff_multiplier
                else:
                    logger.error(f"Max retries ({max_retries}) exceeded")
        
        raise last_exception


class ValidationMixin:
    """
    유효성 검사 믹스인 클래스
    
    에이전트에 유효성 검사 기능을 추가하기 위해 사용합니다.
    """
    
    def _validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]) -> None:
        """
        필수 필드 유효성 검사
        
        Args:
            data: 검사할 데이터
            required_fields: 필수 필드 목록
        
        Raises:
            ValidationError: 필수 필드가 누락된 경우
        """
        from app.services.ai.exceptions import ValidationError
        
        missing = [field for field in required_fields if field not in data or data[field] is None]
        if missing:
            raise ValidationError(
                f"Missing required fields: {', '.join(missing)}",
                context={"missing_fields": missing}
            )
    
    def _validate_field_type(self, data: Dict[str, Any], field: str, expected_type: type) -> None:
        """
        필드 타입 유효성 검사
        
        Args:
            data: 검사할 데이터
            field: 필드 이름
            expected_type: 기대 타입
        
        Raises:
            ValidationError: 타입이 일치하지 않는 경우
        """
        from app.services.ai.exceptions import ValidationError
        
        if field in data and not isinstance(data[field], expected_type):
            raise ValidationError(
                f"Field '{field}' must be of type {expected_type.__name__}",
                field=field,
                expected_type=expected_type.__name__,
                actual_value=data[field]
            )
