from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # database_url: str = "postgresql+psycopg://sunwoo@/drop01?host=/var/run/postgresql&port=5434"
    source_database_url: str = ""
    dropship_database_url: str = ""
    market_database_url: str = ""
    supabase_url: str = "https://tuwqbahkvvidgcbyztop.supabase.co"
    supabase_service_role_key: str = ""
    supabase_bucket: str = "images"

    ownerclan_api_base_url: str = "https://api.ownerclan.com"
    ownerclan_auth_url: str = "https://auth.ownerclan.com/auth"
    ownerclan_graphql_url: str = "https://api.ownerclan.com/v1/graphql"

    ownerclan_primary_user_type: str = "seller"
    ownerclan_primary_username: str = ""
    ownerclan_primary_password: str = ""
    ownerclan_access_key: str = "" 
    ownerclan_secret_key: str = ""

    pricing_default_margin_rate: float = 0.0
    pricing_market_fee_rate: float = 0.13 # 마켓 수수료율 (쿠팡 기본 13%)
    product_processing_name_only: bool = True

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

    
    # AI Settings
    default_ai_provider: str = "ollama" # gemini, ollama, or openai
    
    # Gemini
    gemini_api_key: str = "" # Backwards compatibility
    gemini_api_keys: list[str] = [] # List of keys for rotation
    
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ollama_function_model: str = "functiongemma"
    ollama_embedding_model: str = "embeddinggemma"
    ollama_reasoning_model: str = "rnj-1"
    ollama_vision_model: str = "drop-vision"
    ollama_ocr_model: str = "drop-ocr"
    ollama_qwen_vl_model: str = "drop-qwen-vl"
    ollama_logic_model: str = "granite4"

    # OpenAI
    openai_api_keys: list[str] = [] # List of keys for rotation
    openai_model: str = "gpt-4o-mini"


    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
