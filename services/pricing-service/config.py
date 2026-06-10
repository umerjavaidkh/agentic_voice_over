from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_dsn: str = Field(
        default="postgresql://devuser:devpass@localhost:5432/voice_agent_dev",
        validation_alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    pricing_cache_ttl_seconds: int = 3600


settings = Settings()
