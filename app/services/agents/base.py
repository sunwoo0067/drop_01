from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAgent(ABC):
    """
    모든 AI 에이전트의 기본 인터페이스.
    """
    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}

    @abstractmethod
    def process(self, context: Any) -> Any:
        """에이전트 로직 수행"""
        pass

class CSAgent(BaseAgent):
    """CS 자동화 에이전트 스켈레톤"""
    def process(self, inquiry: Any) -> Any:
        # TODO: Implement AI response logic
        return {"action": "draft_reply", "content": "Hello, thank you for your inquiry."}
