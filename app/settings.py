from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://sunwoo@/drop01?host=/var/run/postgresql&port=5434"
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

    
    # AI Settings
    default_ai_provider: str = "openai" # gemini, ollama, or openai
    
    # Gemini
    gemini_api_key: str = "" # Backwards compatibility
    gemini_api_keys: list[str] = [] # List of keys for rotation
    
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma2"

    # OpenAI
    openai_api_keys: list[str] = [] # List of keys for rotation
    openai_model: str = "gpt-4o-mini"


    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
