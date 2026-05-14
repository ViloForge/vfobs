from functools import lru_cache

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VFOBS_",
        env_file=".env",
        extra="ignore",
    )

    database_url: PostgresDsn
    ingest_token: SecretStr = SecretStr("changeme")
    log_level: str = "INFO"
    service_name: str = "vfobs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
