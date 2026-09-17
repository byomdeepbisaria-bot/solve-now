from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
import os
import urllib.parse

class Settings(BaseSettings):
    # --- Application ---
    PROJECT_NAME: str = "SolveNow"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    SECRET_KEY: str = "dev-only-insecure-secret-key-do-not-use-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- Database ---
    DATABASE_URL: Optional[str] = None
    POSTGRES_SERVER: str = "postgres"
    POSTGRES_USER: str = "solvenow"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "solvenow"
    POSTGRES_PORT: str = "5432"
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20
    POSTGRES_POOL_PRE_PING: bool = True

    # --- Redis ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # --- Object Storage ---
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: str = "solvenow-files"
    S3_REGION: str = "us-east-1"
    S3_PRESIGNED_URL_EXPIRY: int = 3600

    # --- Frontend ---
    NEXT_PUBLIC_API_URL: Optional[str] = None
    NEXT_PUBLIC_APP_URL: Optional[str] = None

    # --- AI Provider ---
    AI_PROVIDER: str = "gemini"
    AI_MODEL: str = "gemini-2.0-flash"
    AI_API_KEY: str = ""

    # --- Monitoring ---
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_ENVIRONMENT: Optional[str] = None

    # --- Worker ---
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # --- Email ---
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@example.com"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_secure_in_production(cls, v: str, info) -> str:
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production" and (len(v) < 32 or "insecure" in v.lower() or v == "CHANGEME"):
            raise ValueError(
                "SECRET_KEY must be a cryptographically random string of 64+ characters in production."
            )
        return v

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            raw = self.DATABASE_URL
            if "://" in raw and "@" in raw:
                scheme, remainder = raw.split("://", 1)
                userinfo, host_part = remainder.rsplit("@", 1)
                if ":" in userinfo:
                    user, pwd = userinfo.split(":", 1)
                    user_unquoted = urllib.parse.unquote(user)
                    pwd_unquoted = urllib.parse.unquote(pwd)
                    user_encoded = urllib.parse.quote_plus(user_unquoted)
                    pwd_encoded = urllib.parse.quote_plus(pwd_unquoted)
                    if scheme in ("postgresql", "postgres"):
                        scheme = "postgresql+pg8000"
                    return f"{scheme}://{user_encoded}:{pwd_encoded}@{host_part}"
            return raw

        # Prevent "user@hostname" parsing bugs when passwords contain @
        user = urllib.parse.quote_plus(urllib.parse.unquote(self.POSTGRES_USER))
        password = urllib.parse.quote_plus(urllib.parse.unquote(self.POSTGRES_PASSWORD))
        return (
            f"postgresql+pg8000://{user}:{password}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_CONNECTION_URL(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            pwd = urllib.parse.quote_plus(self.REDIS_PASSWORD)
            return f"redis://:{pwd}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
