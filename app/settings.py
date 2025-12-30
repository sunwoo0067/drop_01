from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # database_url: str = "postgresql+psycopg://sunwoo@/drop01?host=/var/run/postgresql&port=5434"
    source_database_url: str = ""
    dropship_database_url: str = ""
    market_database_url: str = ""
    supabase_url: str = "https://irxsnhaqathvumbflzme.supabase.co"
    supabase_service_role_key: str = ""
    supabase_bucket: str = "images"

    ownerclan_api_base_url: str = "https://api.ownerclan.com"
    ownerclan_auth_url: str = "https://auth.ownerclan.com/auth"
    ownerclan_graphql_url: str = "https://api.ownerclan.com/v1/graphql"
    ownerclan_use_sef_proxy: bool = True 


    ownerclan_primary_user_type: str = "seller"
    ownerclan_primary_username: str = ""
    ownerclan_primary_password: str = ""
    ownerclan_access_key: str = "" 
    ownerclan_secret_key: str = ""

    pricing_default_margin_rate: float = 0.0
    pricing_market_fee_rate: float = 0.13 # 마켓 수수료율 (쿠팡 기본 13%)
    product_processing_name_only: bool = True
    
    # Coupang Testing
    coupang_bulk_try: str = "0"
    coupang_research_ignore_skip_log: str = "0"
    coupang_research_ignore_doc_pending: str = "0"
    coupang_fallback_category_codes: str = "77800,77797,77795"
    coupang_daily_limit: int = 50
    coupang_fallback_ratio_threshold: float = 0.3
    coupang_stability_mode: bool = False
    coupang_fallback_cooldown_threshold: int = 50
    coupang_fallback_cooldown_days: int = 7
    coupang_sourcing_policy_mode: str = "shadow" # shadow, enforce_lite, enforce
    coupang_stability_declination_threshold: float = 0.3 # 30%p 하락 시 가드레일 작동
    coupang_block_surge_threshold: float = 2.0 # BLOCK 비율 200% 증가 시 알림

    product_name_forbidden_keywords: list[str] = [
        "정품",
        "오리지널",
        "100%",
        "최고",
        "최상",
        "리미티드",
        "초특가",
        "특가",
        "핫딜",
        "무료배송",
        "당일",
        "익일",
        "즉시",
        "예약",
        "한정",
        "사은품",
        "증정",
        "덤",
        "세일",
        "할인",
        "%",
        "원가",
        "최저가",
        "이벤트",
        "KC",
        "인증",
        "허가",
    ]
    product_name_replacements: dict[str, str] = {
        "호환용": "호환",
        "교체용": "교체",
        "재생토너": "토너",
        "정품호환": "호환",
        "블랙": "검정",
        "옐로우": "노랑",
        "마젠타": "빨강",
        "시안": "파랑",
    }

    
    # 성능 최적화 설정
    processing_concurrent_limit: int = 20  # 상품 가공 병렬 처리 수
    image_download_concurrent: int = 5     # 이미지 다운로드 동시성
    few_shot_cache_ttl: int = 300         # Few-shot 예제 캐시 TTL (초)
    api_key_cache_ttl: int = 600          # API 키 캐시 TTL (초)
    
    # AI Settings
    default_ai_provider: str = "ollama" # gemini, ollama, or openai
    
    # Gemini
    gemini_api_key: str = "" # Backwards compatibility
    gemini_api_keys: list[str] = [] # List of keys for rotation
    
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"  # gemma3:4b → qwen3:8b (최신 모델로 업그레이드)
    ollama_function_model: str = "functiongemma"
    ollama_embedding_model: str = "qwen3-embedding"  # embeddinggemma → qwen3-embedding (최신 모델로 업그레이드)
    ollama_reasoning_model: str = "rnj-1"
    ollama_vision_model: str = "qwen3-vl:8b"  # drop-vision → qwen3-vl:8b (최신 모델로 업그레이드)
    ollama_ocr_model: str = "drop-ocr"
    ollama_qwen_vl_model: str = "qwen3-vl:8b"  # drop-qwen-vl → qwen3-vl:8b (최신 모델로 업그레이드)
    ollama_logic_model: str = "qwen3:8b"  # granite4 → qwen3:8b (최신 모델로 업그레이드)

    # OpenAI
    openai_api_keys: list[str] = [] # List of keys for rotation
    openai_model: str = "gpt-4o-mini"

    # Stable Diffusion (Automatic1111 / Forge / etc)
    sd_api_url: str = "http://localhost:7860"
    sd_model_name: str = "v1-5-pruned-emaonly.safetensors"


    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
