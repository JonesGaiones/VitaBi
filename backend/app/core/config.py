"""
Configuração central da aplicação.
Lê do ambiente, valida com Pydantic, expõe um singleton `settings`.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_NAME: str = "Vita BI"
    ENVIRONMENT: str = "development"   # development | staging | production
    DEBUG: bool = False

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 900       # 15 min

    # Security
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 8   # 8h

    # Notifications
    WEBHOOK_SLACK_URL: str = ""

    # QuickBooks API (optional for local dev without QB integration)
    QB_CLIENT_ID: str = ""
    QB_CLIENT_SECRET: str = ""
    QB_REFRESH_TOKEN: str = ""
    QB_REALM_ID: str = ""
    QB_ENVIRONMENT: str = "production"   # sandbox | production
    QB_BASE_URL: str = "https://quickbooks.api.intuit.com"

    # ETL
    DE_PARA_DIR: str = "/app/data/de_para"
    RAW_DIR: str = "/app/data/raw"
    PROCESSED_DIR: str = "/app/data/processed"

    # Insights thresholds
    CHURN_SIGMA_THRESHOLD: float = 1.5      # cliente é alerta se atraso > média + 1.5σ
    PRICE_ANOMALY_SIGMA: float = 2.0        # preço < média - 2σ aciona alerta
    SLOW_MOVER_DAYS_COVER: int = 180        # >180 dias de estoque = desova

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
