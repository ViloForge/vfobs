from functools import lru_cache

from pydantic import HttpUrl, PostgresDsn, SecretStr
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

    # WG2-T0 (read side). Deviation D-T0-1 vs AC-T0-6's literal "no
    # default": kept Optional so the ~67 WG1 test fixtures that build
    # Settings(...) directly don't regress. The "must be set in prod /
    # app fails to start" guarantee is preserved by VtfClient.__init__
    # raising when this is None (production VtfClient is constructed in
    # main.py:_lifespan, so an unconfigured prod app fails to start).
    vtaskforge_url: HttpUrl | None = None
    vtaskforge_timeout_seconds: int = 5


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
