import logging
import asyncio
from typing import Callable, Dict, List, Any, Coroutine

logger = logging.getLogger(__name__)

class EventBus:
    """
    내부 컴포넌트 간 비동기 연동을 위한 경량 이벤트 버스.
    에이전트 연동 및 상태 변경 통지에 활용 가능.
    """
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        """이벤트 구독 등록"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"[EVENT] Subscribed to {event_type}")

    async def publish(self, event_type: str, data: Any):
        """이벤트 발행"""
        logger.info(f"[EVENT] Publishing {event_type}")
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        # 모든 핸들러를 비동기로 실행
        tasks = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(data))
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[EVENT] Error preparing handler for {event_type}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"[EVENT] Exception in async handler: {res}")

# 싱글톤 인스턴스
bus = EventBus()
