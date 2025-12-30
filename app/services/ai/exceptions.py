"""
AI Agent Exception Classes

구조화된 에러 처리를 위한 예외 클래스 정의
"""
from typing import Optional, Dict, Any
from enum import Enum


class ErrorSeverity(Enum):
    """에러 심각도 레벨"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentError(Exception):
    """
    Base exception for all agent errors
    
    Attributes:
        message: 에러 메시지
        error_code: 에러 코드
        severity: 에러 심각도
        context: 추가 컨텍스트 정보
        recoverable: 복구 가능 여부
    """
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = False
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.severity = severity
        self.context = context or {}
        self.recoverable = recoverable
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """에러 정보를 딕셔너리로 변환"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "severity": self.severity.value,
            "context": self.context,
            "recoverable": self.recoverable
        }


class APIError(AgentError):
    """
    External API call failures
    
    Attributes:
        status_code: HTTP 상태 코드
        url: 요청 URL
        response_body: 응답 본문
    """
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        url: Optional[str] = None,
        response_body: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        **kwargs
    ):
        context = {
            "status_code": status_code,
            "url": url,
            "response_body": response_body
        }
        context.update(kwargs) # 나머지 인자들도 컨텍스트에 포함
        super().__init__(
            message=message,
            error_code="API_ERROR",
            severity=severity,
            context=context,
            recoverable=recoverable
        )
        self.status_code = status_code
        self.url = url
        self.response_body = response_body


class DatabaseError(AgentError):
    """
    Database operation failures
    
    Attributes:
        table_name: 영향받은 테이블 이름
        query: 실패한 쿼리
        operation: 수행하려던 작업 (insert, update, delete, select)
    """
    
    def __init__(
        self,
        message: str,
        table_name: Optional[str] = None,
        query: Optional[str] = None,
        operation: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        recoverable: bool = False,
        **kwargs
    ):
        context = {
            "table_name": table_name,
            "query": query,
            "operation": operation
        }
        context.update(kwargs)
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            severity=severity,
            context=context,
            recoverable=recoverable
        )
        self.table_name = table_name
        self.query = query
        self.operation = operation


class AIError(AgentError):
    """
    AI service failures
    
    Attributes:
        provider: AI 제공자 (openai, gemini, ollama)
        model: 사용된 모델
        prompt: 실패한 프롬프트
        fallback_available: 폴백 제공자 사용 가능 여부
    """
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        fallback_available: bool = False,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        **kwargs
    ):
        context = {
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "fallback_available": fallback_available
        }
        context.update(kwargs)
        super().__init__(
            message=message,
            error_code="AI_ERROR",
            severity=severity,
            context=context,
            recoverable=recoverable
        )
        self.provider = provider
        self.model = model
        self.prompt = prompt
        self.fallback_available = fallback_available


class ValidationError(AgentError):
    """
    Input validation failures
    
    Attributes:
        field: 실패한 필드 이름
        expected_type: 기대 타입
        actual_value: 실제 값
        constraints: 위배된 제약조건
    """
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None,
        constraints: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.LOW,
        recoverable: bool = False,
        **kwargs
    ):
        context = {
            "field": field,
            "expected_type": expected_type,
            "actual_value": str(actual_value) if actual_value is not None else None,
            "constraints": constraints or {}
        }
        context.update(kwargs)
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            severity=severity,
            context=context,
            recoverable=recoverable
        )
        self.field = field
        self.expected_type = expected_type
        self.actual_value = actual_value
        self.constraints = constraints


class WorkflowError(AgentError):
    """
    Workflow execution failures
    
    Attributes:
        workflow_name: 워크플로우 이름
        step: 실패한 단계
        state: 실패 시점의 상태
    """
    
    def __init__(
        self,
        message: str,
        workflow_name: Optional[str] = None,
        step: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        recoverable: bool = False,
        **kwargs
    ):
        context = {
            "workflow_name": workflow_name,
            "step": step,
            "state": state
        }
        context.update(kwargs)
        super().__init__(
            message=message,
            error_code="WORKFLOW_ERROR",
            severity=severity,
            context=context,
            recoverable=recoverable
        )
        self.workflow_name = workflow_name
        self.step = step
        self.state = state


class RetryableError(AgentError):
    """
    일시적 오류로 재시도 가능한 에러
    
    네트워크 타임아웃, 일시적 서버 오류 등
    """
    
    def __init__(
        self,
        message: str,
        retry_count: int = 0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        context.update({
            "retry_count": retry_count,
            "max_retries": max_retries,
            "backoff_seconds": backoff_seconds
        })
        super().__init__(
            message=message,
            error_code="RETRYABLE_ERROR",
            severity=ErrorSeverity.LOW,
            context=context,
            recoverable=True
        )
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds


class TimeoutError(AgentError):
    """
    Operation timeout errors
    """
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        **kwargs
    ):
        context = {
            "operation": operation,
            "timeout_seconds": timeout_seconds
        }
        context.update(kwargs)
        super().__init__(
            message=message,
            error_code="TIMEOUT_ERROR",
            severity=severity,
            context=context,
            recoverable=recoverable
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds


def wrap_exception(
    error: Exception,
    error_class: type = AgentError,
    **kwargs
) -> AgentError:
    """
    일반 예외를 구조화된 에이전트 예외로 래핑
    
    Args:
        error: 원래 예외
        error_class: 래핑할 에이전트 예외 클래스
        **kwargs: 에이전트 예외 생성자에 전달할 추가 인자
    
    Returns:
        래핑된 AgentError 인스턴스
    """
    message = str(error)
    if isinstance(error, AgentError):
        return error
    
    # 이미 AgentError인 경우 그대로 반환
    if isinstance(error, AgentError):
        return error
    
    # 에러 타입에 따라 적절한 래퍼 선택
    if "timeout" in message.lower() or "timed out" in message.lower():
        return TimeoutError(message, **kwargs)
    elif "connection" in message.lower() or "network" in message.lower():
        return APIError(message, **kwargs)
    elif "database" in message.lower() or "sql" in message.lower():
        return DatabaseError(message, **kwargs)
    elif "validation" in message.lower() or "invalid" in message.lower():
        return ValidationError(message, **kwargs)
    
    return error_class(message, **kwargs)
