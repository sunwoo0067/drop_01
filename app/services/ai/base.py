from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """
        Generates simple text response.
        """
        pass

    @abstractmethod
    def generate_json(self, prompt: str) -> Dict[str, Any] | List[Any]:
        """
        Generates structured JSON response.
        """
        pass
