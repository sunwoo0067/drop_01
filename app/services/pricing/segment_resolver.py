import hashlib
import uuid
from typing import Optional

class SegmentResolver:
    """
    상품 및 마켓 차원을 기반으로 자율성 관리 단위인 '세그먼트'를 식별합니다.
    """
    
    def resolve_segment_metadata(
        self, 
        vendor: str, 
        channel: str, 
        category_code: Optional[str], 
        strategy_id: Optional[uuid.UUID], 
        lifecycle_stage: str
    ) -> dict:
        """
        세그먼트 구성 요소들을 정규화하여 반환합니다.
        """
        return {
            "vendor": vendor,
            "channel": channel,
            "category_code": category_code,
            "strategy_id": strategy_id,
            "lifecycle_stage": lifecycle_stage
        }

    def get_segment_key(self, metadata: dict) -> str:
        """
        세그먼트 메타데이터를 기반으로 고유한 Hash 키를 생성합니다.
        """
        # 정렬된 키를 사용하여 결정론적 해시 생성
        components = [
            f"v:{metadata['vendor']}",
            f"ch:{metadata['channel']}",
            f"cat:{metadata['category_code'] or 'NULL'}",
            f"st:{str(metadata['strategy_id']) if metadata['strategy_id'] else 'NULL'}",
            f"lc:{metadata['lifecycle_stage']}"
        ]
        raw_str = "|".join(components)
        return hashlib.sha256(raw_str.encode()).hexdigest()
