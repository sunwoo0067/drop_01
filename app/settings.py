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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
