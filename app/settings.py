from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://sunwoo@/drop01?host=/var/run/postgresql&port=5434"
    supabase_url: str = "https://tuwqbahkvvidgcbyztop.supabase.co"
    supabase_service_role_key: str = ""
    supabase_bucket: str = "images"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
