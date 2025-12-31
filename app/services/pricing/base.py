from abc import ABC, abstractmethod
from typing import Any, Dict

class BasePricingEngine(ABC):
    """
    동적 가격 책정 엔진의 기본 인터페이스.
    """
    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}

    @abstractmethod
    def calculate_price(self, product_context: Any) -> int:
        """최적 가격 산출"""
        pass

class SimpleMarkupEngine(BasePricingEngine):
    """단순 마진 기반 가격 엔진 스켈레톤"""
    def calculate_price(self, product_context: Any) -> int:
        cost = product_context.get("cost", 0)
        margin = self.config.get("default_margin", 1.2)
        return int(cost * margin)
