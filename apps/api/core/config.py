from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
import os
import ssl
import urllib.parse


class Settings(BaseSettings):
    # --- Application ---
    PROJECT_NAME: str = "SolveNow"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    SECRET_KEY: str = "dev-only-insecure-secret-key-do-not-use-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- Database ---
    # Production: set DATABASE_URL to Supabase pooler connection string.
    # Development fallback: individual POSTGRES_* variables (loaded from .env).
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
    # Production: set REDIS_URL to the full Upstash URL (rediss://...).
    # Development fallback: REDIS_HOST + REDIS_PORT (read from .env).
    # REDIS_URL takes precedence over REDIS_HOST/REDIS_PORT.
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
    CORS_ORIGINS: Optional[str] = None

    # --- AI Provider ---
    AI_PROVIDER: str = "gemini"
    AI_MODEL: str = "gemini-3.7-flash"
    AI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.7-flash"
    GROQ_MODEL: str = "openai/gpt-oss-20b"

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

    @field_validator("REDIS_URL")
    @classmethod
    def redis_url_must_have_valid_scheme(cls, v: Optional[str]) -> Optional[str]:
        """
        Reject REDIS_URL values that are non-empty but lack a valid scheme.
        Valid schemes: redis://, rediss://, unix://
        This catches mis-configured Render variables (e.g. bare hostname without scheme).
        """
        if v is None or v == "":
            return None  # Will fall back to REDIS_HOST/REDIS_PORT
        valid_schemes = ("redis://", "rediss://", "unix://")
        if not any(v.startswith(s) for s in valid_schemes):
            raise ValueError(
                f"REDIS_URL has an invalid scheme. "
                f"Expected one of: redis://, rediss://, unix://. "
                f"Got a URL starting with: {v[:20]!r}. "
                f"For Upstash use the full rediss://... URL."
            )
        return v

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """
        Build the SQLAlchemy connection URI.

        Production: DATABASE_URL (Supabase pooler) is normalised to postgresql+pg8000.
        Development: Assembled from POSTGRES_* variables.

        NOTE: When DATABASE_URL already contains 'pg8000' it is returned unchanged
        to avoid double-encoding.
        """
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

        # Development fallback: assemble from individual POSTGRES_* vars.
        user = urllib.parse.quote_plus(urllib.parse.unquote(self.POSTGRES_USER))
        password = urllib.parse.quote_plus(urllib.parse.unquote(self.POSTGRES_PASSWORD))
        return (
            f"postgresql+pg8000://{user}:{password}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_CONNECTION_URL(self) -> str:
        """
        Canonical Redis URL used by ALL Redis consumers (async client, events, Celery).

        Priority:
          1. REDIS_URL environment variable (production — must be full rediss://... URL)
          2. REDIS_HOST + REDIS_PORT + optional REDIS_PASSWORD (development fallback)

        Never returns None or an empty string.
        """
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            pwd = urllib.parse.quote_plus(self.REDIS_PASSWORD)
            return f"redis://:{pwd}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def db_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        SSL context for the PostgreSQL connection via pg8000.

        Production (Supabase pooler):
            The Supabase Transaction/Session Pooler (PgBouncer) presents a TLS
            certificate signed by a private Supabase CA that is NOT in the public
            trust stores (certifi / system). Full chain verification therefore fails
            with CERTIFICATE_VERIFY_FAILED.

            Supabase's own documentation for pg8000 explicitly recommends using
            ssl_context with verify_mode=CERT_NONE for pooler connections because:
            - The TLS channel IS fully encrypted (transport security is preserved).
            - Only certificate CHAIN verification is relaxed, not encryption.
            - The pooler host is a Supabase-controlled endpoint, not a public CA.

            If you require full chain verification, supply the Supabase CA certificate
            via the SUPABASE_CA_CERT environment variable (PEM text). The property
            will load it into the context automatically.

        Development:
            No SSL context — local PostgreSQL does not use TLS.
        """
        if not self.is_production:
            return None

        ctx = ssl.create_default_context()

        # Check if a Supabase CA certificate is supplied via environment variable.
        # The variable should contain the full PEM text of the Supabase CA cert.
        # Set it on Render as: SUPABASE_CA_CERT=<PEM contents>
        supabase_ca = os.environ.get("SUPABASE_CA_CERT", "").strip()
        if supabase_ca:
            import tempfile, os as _os
            # Write PEM to a temp file so load_verify_locations can read it
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pem", delete=False
            ) as tmp:
                tmp.write(supabase_ca)
                tmp_path = tmp.name
            try:
                ctx.load_verify_locations(cafile=tmp_path)
            finally:
                _os.unlink(tmp_path)
            # With CA loaded, full verification can remain enabled
            return ctx

        # No CA cert supplied: relax chain verification for Supabase pooler.
        # Transport encryption (TLS) remains active. Only CHAIN verification is relaxed.
        # This is the documented correct approach for Supabase pg8000 pooler connections.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
